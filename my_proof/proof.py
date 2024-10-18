import json
import logging
import os
from typing import Dict, Any

import requests
import gc
import re
import pandas as pd
import hashlib
import math
import json

from my_proof.models.proof_response import ProofResponse
from .verify import DbSNPHandler


class TwentyThreeWeFileScorer:
    header_template = """
    # This file contains raw genotype data, including data that is not used in 23andMe reports.
    # This data has undergone a general quality review however only a subset of markers have been 
    # individually validated for accuracy. As such, this data is suitable only for research, 
    # educational, and informational use and not for medical or other use.
    # 
    # Below is a text version of your data.  Fields are TAB-separated
    # Each line corresponds to a single SNP.  For each SNP, we provide its identifier 
    # (an rsid or an internal id), its location on the reference human genome, and the 
    # genotype call oriented with respect to the plus strand on the human reference sequence.
    # We are using reference human assembly build 37 (also known as Annotation Release 104).
    # Note that it is possible that data downloaded at different times may be different due to ongoing 
    # improvements in our ability to call genotypes. More information about these changes can be found at:
    #
    # More information on reference human assembly builds:
    # https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13/
    #
    # rsid	chromosome	position	genotype
    """
    valid_genotypes = set("ATCG-ID")
    valid_chromosomes = set([str(i) for i in range(1, 23)] + ["X", "Y", "MT"])

    def __init__(self, input_data, config):
        self.input_data = input_data
        self.profile_id = self.get_profile_id(input_data)
        self.config = config
        self.proof_response = None
        self.hash = None
        self.sender_address = None

    @staticmethod
    def get_profile_id(input_data):
        file_content = "\n".join([d for d in input_data[:50]])

        # Define the URL pattern you're looking for
        url_prefix = 'https://you.23andme.com/p/'
        url_suffix = '/tools/data/download/'

        # Find the starting position of the URL pattern
        start_index = file_content.find(url_prefix)
        if start_index == -1:
            return None  # URL not found

        # Find the ending position of the profile ID (end of the URL)
        end_index = file_content.find(url_suffix, start_index)
        if end_index == -1:
            return None  # URL suffix not found

        # Extract the profile ID between the URL prefix and suffix
        profile_id_start = start_index + len(url_prefix)
        profile_id = file_content[profile_id_start:end_index]

        # Return the profile ID if found, otherwise None
        if profile_id:
            return profile_id
        else:
            return None

    def read_header(self):
        header_lines = []
        for line in self.input_data:
            if line.startswith("#") or line.startswith("rsid"):  # Capture header lines
                # Ignore timestamp and profile-specific URL lines using regex
                if re.match(r"# This data file generated by 23andMe at:", line):
                    continue  # Skip unique timestamp line
                if re.match(r"# https://you\.23andme\.com/p/", line):
                    continue  # Skip unique download link line
                header_lines.append(line.strip())
            else:
                break  # Stop reading after headers
        header = "\n".join(header_lines[1:])
        return header

    def check_header(self):
        file_header = self.read_header()

        clean_template = "\n".join([line.strip() for line in self.header_template.strip().split("\n") if """https://you.23andme.com""" not in line])
        clean_file_header = file_header.strip()

        return clean_template == clean_file_header

    def check_rsid_lines(self):
        invalid_rows = []

        line_number = 1
        for line in self.input_data:
            line = line.strip()
            if "#" in line:
                continue
            if not line:
                print(f"File ended unexpectedly at line {line_number}.")
                return False

            columns = line.split("\t")
            if len(columns) != 4:
                print(f"Line {line_number} does not have exactly 4 columns: {line}")
                return False

            rsid, chromosome, position, genotype = columns
            row = (rsid, chromosome, position, genotype)

            # Check if rsid starts with 'rs' or 'i' and ends in digits
            if not re.match(r'^(rs|i)\d+$', rsid):
                print(f"Line {line_number}: Invalid rsid format: {rsid}")
                invalid_rows.append(row)

            # Check if chromosome is one of 1-23, X, Y, or MT
            if chromosome not in self.valid_chromosomes:
                print(f"Line {line_number}: Invalid chromosome value: {chromosome}")
                invalid_rows.append(row)

            # Check if the genotype contains only valid characters
            if any(char not in self.valid_genotypes for char in genotype):
                print(f"Line {line_number}: Invalid genotype characters: {genotype}")
                invalid_rows.append(row)

            line_number += 1
        if invalid_rows:
            return False
        return True

    def verify_profile(self):
        """
        Sends the profile id for verification via a POST request.
        """
        self.sender_address = self.config['verify'].split('address=')[-1]
        url = f"{self.config['verify']}&profile_id={self.profile_id}"
        response = requests.get(url=url)
        resp = response.json()
        profile_verified = resp.get('is_approved', False)

        return profile_verified

    def verify_hash(self, genome_hash):
        """
        Sends the hashed genome data for verification via a POST request.
        """
        url = f"{self.config['key']}&genome_hash={genome_hash}"
        response = requests.get(url=url)
        resp = response.json()
        hash_unique = resp.get('is_unique', False)

        return hash_unique

    def hash_23andme_file(self, file_path):
        # Read the 23andMe file into a DataFrame, skipping the comment lines
        df = pd.read_csv(file_path, sep='\t', comment='#', names=['rsid', 'chromosome', 'position', 'genotype'])

        # Remove rows where the rsid starts with 'i'
        df_filtered = df[~df['rsid'].str.startswith('i')]

        # Sort the DataFrame by the rsid column
        df_sorted = df_filtered.sort_values(by='rsid')

        # Concatenate the rows into one large symbol-separated string
        concatenated_string = '|'.join(
            df_sorted.apply(lambda row: f"{row['rsid']}:{row['chromosome']}:{row['position']}:{row['genotype']}",
                            axis=1))

        # Delete the DataFrame to free up memory
        del df, df_filtered, df_sorted
        gc.collect()  # Force garbage collection

        # Hash the concatenated string using SHA-256
        hash_object = hashlib.sha256(concatenated_string.encode())
        hash_hex = hash_object.hexdigest()
        self.hash = hash_hex

        return hash_hex

    @staticmethod
    def invalid_genotypes_score(total: int, low: int = 1, high: int = 3):
        if total <= low:
            return 1.0
        elif total >= high:
            return 0.0
        else:
            return 1.0 - (total - low) / (high - low)

    @staticmethod
    def indel_score(total, low: int = 3, ultra_low: int = 1, high: int = 13, ultra_high: int = 22):
        if total <= ultra_low:
            return 0.0
        elif ultra_low < total <= low:
            return (total - ultra_low) / (low - ultra_low)
        elif low < total <= high:
            return 1.0
        elif high < total <= ultra_high:
            return (ultra_high - total) / (ultra_high - high)
        else:
            return 0.0

    @staticmethod
    def i_rsid_score(total: int, low: int = 5, high: int = 25):
        if total <= low:
            return 1.0
        elif total >= high:
            return 0.0
        else:
            return 0.5

    @staticmethod
    def percent_verification_score(verified: int, all: int, low: float = 0.9, ultra_low: float = 0.85,
                                   high: float = 0.96, ultra_high: float = 0.98):
        verified_ratio = verified / all

        if low <= verified_ratio <= high:
            return 1.0
        elif ultra_low < verified_ratio < low:
            return (verified_ratio - ultra_low) / (low - ultra_low)
        elif high < verified_ratio <= ultra_high:
            return (ultra_high - verified_ratio) / (ultra_high - high)
        elif verified_ratio > ultra_high:
            return 0.0
        else:
            return 0.0

    def save_hash(self, proof_response):

        hash_data = self.generate_hash_save_data(proof_response)
        response = requests.post(url=self.config['key'], data=hash_data)
        resp = response.json()
        success = resp.get('success', False)

        return success

    def generate_hash_save_data(self, proof_response):
        hash_save_data = {
            'sender_address': self.sender_address,
            'attestor_address': '',
            'tee_url': '',
            'job_id': '',
            'file_id': '',
            'profile_id': self.profile_id,
            'genome_hash': self.hash,
            'authenticity_score': proof_response.authenticity,
            'ownership_score': proof_response.ownership,
            'uniqueness_score': proof_response.uniqueness,
            'quality_score': proof_response.quality,
            'total_score': proof_response.attributes['total_score'],
            'score_threshold': proof_response.attributes['score_threshold'],
            'is_valid': proof_response.valid
        }

        return hash_save_data

    def proof_of_ownership(self) -> float:
        validated = self.verify_profile()
        if validated:
            return 1.0
        else:
            return 0

    def proof_of_quality(self, filepath) -> float:

        dbsnp = DbSNPHandler(self.config)
        results = dbsnp.dbsnp_verify(filepath)

        invalid_score = self.invalid_genotypes_score(results['invalid_genotypes'])
        indel_score = self.indel_score(results['indels'])
        i_rsid_score = self.i_rsid_score(results['i_rsids'])
        percent_verify_score = self.percent_verification_score(results['dbsnp_verified'], results['all'])

        quality_score = 0.4 * invalid_score + 0.3 * percent_verify_score + 0.2 * indel_score + 0.1 * i_rsid_score

        return quality_score

    def proof_of_uniqueness(self, filepath) -> float:

        hashed_dna = self.hash_23andme_file(filepath)
        unique = self.verify_hash(hashed_dna)

        if unique:
            return 1.0
        else:
            return 0

    def proof_of_authenticity(self) -> float:
        header_ok = self.check_header()
        rsids_ok = self.check_rsid_lines()
        if header_ok and rsids_ok:
            return 1.0
        else:
            return 0


class Proof:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.proof_response = ProofResponse(dlp_id=config['dlp_id'])

    def generate(self) -> ProofResponse:
        """Generate proofs for all input files."""
        logging.info("Starting proof generation")

        scorer = None
        twenty_three_file = None

        for input_filename in os.listdir(self.config['input_dir']):
            input_file = os.path.join(self.config['input_dir'], input_filename)
            with open(input_file, 'r') as i_file:

                if input_filename.split('.')[-1] == 'txt':
                    twenty_three_file = input_file
                    input_data = [f for f in i_file]
                    scorer = TwentyThreeWeFileScorer(input_data=input_data, config=self.config)
                    break

        score_threshold = 0.9

        self.proof_response.uniqueness = scorer.proof_of_uniqueness(filepath=twenty_three_file)
        self.proof_response.ownership = scorer.proof_of_ownership()
        self.proof_response.authenticity = scorer.proof_of_authenticity()
        self.proof_response.quality = scorer.proof_of_quality(filepath=twenty_three_file)

        # Calculate overall score and validity
        total_score = (0.25 * self.proof_response.quality + 0.25 * self.proof_response.ownership +
                       0.25 * self.proof_response.authenticity + 0.25 * self.proof_response.uniqueness)
        self.proof_response.score = total_score
        self.proof_response.valid = total_score >= score_threshold

        # Additional (public) properties to include in the proof about the data
        self.proof_response.attributes = {
            'total_score': total_score,
            'score_threshold': score_threshold,
        }

        # Additional metadata about the proof, written onchain
        self.proof_response.metadata = {
            'dlp_id': self.config['dlp_id'],
        }

        save_successful = scorer.save_hash(self.proof_response)

        if save_successful:
            print("Hash Data Saved Successfully.")
        else:
            raise Exception("Hash Data Saving Failed.")

        return self.proof_response
