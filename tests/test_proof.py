
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch, Mock
from io import StringIO
import pandas as pd

from my_proof.proof import Proof, TwentyThreeWeFileScorer
from my_proof.verify import DbSNPHandler

from .conftest import mock_requester

from .data_tables import (ProfileIdInputData, HeaderTestData, RSIDTestData, ProfileVerifyTestData, HashVerifyTestData,
                          InvalidGenotypesScoreTestData, IndelScoreTestData, IRsidScoreTestData, ProofResponse,
                          PercentVerifyScoreTestData, HashSaveDataTestData, ProofOfOwnershipTestData,
                          ProofOfQualityTestData, ProofOfUniquenessTestData, ProofOfAuthenticityTestData,
                          ReadHeaderTestData, Hash23AndMeFileTestData, SaveHashTestData, GenerateTestData)


class TestTwentyThreeWeFileScorer:

    @pytest.mark.parametrize("input_data", [
        ProfileIdInputData(data=[
            "# https://you.23andme.com/p/abc123/tools/data/download/",
            "rsid\tchromosome\tposition\tgenotype"
        ], expected_profile_id="abc123"),
        ProfileIdInputData(data=[
            "# Some other random data",
            "rsid\tchromosome\tposition\tgenotype"
        ], expected_profile_id=None),
        ProfileIdInputData(data=[
            "# https://you.23andme.com/p/xyz456/tools/data/download/",
            "rsid\tchromosome\tposition\tgenotype"
        ], expected_profile_id="xyz456")
    ])
    def test_get_profile_id(self, input_data):
        scorer = TwentyThreeWeFileScorer(input_data.data, config={}, requester=None, hasher=None)
        assert scorer.get_profile_id(input_data.data) == input_data.expected_profile_id

    @pytest.mark.parametrize("input_data", [
        HeaderTestData(data=[
            "# This data file generated by 23andMe at: Wed Sep 11 21:58:51 2024",
            "#",
            "# This file contains raw genotype data, including data that is not used in 23andMe reports.",
            "# This data has undergone a general quality review however only a subset of markers have been ",
            "# individually validated for accuracy. As such, this data is suitable only for research, ",
            "# educational, and informational use and not for medical or other use.",
            "#",
            "# Below is a text version of your data.  Fields are TAB-separated",
            "# Each line corresponds to a single SNP.  For each SNP, we provide its identifier ",
            "# (an rsid or an internal id), its location on the reference human genome, and the ",
            "# genotype call oriented with respect to the plus strand on the human reference sequence.",
            "# We are using reference human assembly build 37 (also known as Annotation Release 104).",
            "# Note that it is possible that data downloaded at different times may be different due to ongoing ",
            "# improvements in our ability to call genotypes. More information about these changes can be found at:",
            "# https://you.23andme.com/p/alda223kl32siadkn/tools/data/download/",
            "#",
            "# More information on reference human assembly builds:",
            "# https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13/",
            "#",
            "# rsid\tchromosome\tposition\tgenotype"
        ], header_included=True, expected_check_header=True),

        HeaderTestData(data=[
            "# Invalid file content",
            "rsid\tchromosome\tposition\tgenotype"
        ], header_included=False, expected_check_header=False)
    ])
    def test_check_header(self, input_data):
        scorer = TwentyThreeWeFileScorer(input_data.data, config={}, requester=None, hasher=None)
        result = scorer.check_header()
        assert result == input_data.expected_check_header

    @pytest.mark.parametrize("input_data", [
        RSIDTestData(data=[
            "rs17221409\t4\t173148462\tAA",
            "rs36015135\t17\t59924191\tTT"
        ], expected_check_rsid_lines=True),

        RSIDTestData(data=[
            "invalid_line",
            "rs123456\tX\t12345\tAA"
        ], expected_check_rsid_lines=False),

        RSIDTestData(data=[
            "rs8965392\tY\t54321\tINVALID_GENOTYPE"
        ], expected_check_rsid_lines=False)
    ])
    def test_check_rsid_lines(self, input_data):
        scorer = TwentyThreeWeFileScorer(input_data.data, config={}, requester=None, hasher=None)
        result = scorer.check_rsid_lines()
        assert result == input_data.expected_check_rsid_lines

    @pytest.mark.parametrize("input_data", [
        ProfileVerifyTestData(profile_id="abc123", mock_response={'is_approved': True},
                              expected_verification=True),
        ProfileVerifyTestData(profile_id="xyz456", mock_response={'is_approved': False},
                              expected_verification=False)
    ])
    def test_verify_profile(self, input_data, mock_requester):
        config = {'verify': f"https://example.com/verify?address=abc"}
        input_data_lines = [f"# https://you.23andme.com/p/{input_data.profile_id}/tools/data/download/"]
        mock_requester.get.return_value.json.return_value = input_data.mock_response

        scorer = TwentyThreeWeFileScorer(input_data_lines, config, requester=mock_requester, hasher=None)
        assert scorer.verify_profile() == input_data.expected_verification

    @pytest.mark.parametrize("input_data", [
        HashVerifyTestData(genome_hash="abc_hash", mock_response={'is_unique': True},
                                 expected_hash_verification=True),
        HashVerifyTestData(genome_hash="xyz_hash", mock_response={'is_unique': False},
                                 expected_hash_verification=False)
    ])
    def test_verify_hash(self, input_data, mock_requester):
        config = {'key': "https://example.com/key"}
        mock_requester.get.return_value.json.return_value = input_data.mock_response

        scorer = TwentyThreeWeFileScorer(input_data=[], config=config, requester=mock_requester, hasher=None)
        assert scorer.verify_hash(input_data.genome_hash) == input_data.expected_hash_verification

    # @pytest.mark.parametrize("input_data", [
    #     Hash23AndMeFileTestData(
    #         file_path="/mock/file/path",
    #         mock_df_rows=[
    #             {"rsid": "rs1", "chromosome": "chr1", "position": "pos1", "genotype": "AA"},
    #             {"rsid": "rs2", "chromosome": "chr2", "position": "pos2", "genotype": "TT"}
    #         ],
    #         expected_concatenated_string="rs1:chr1:pos1:AA|rs2:chr2:pos2:TT",
    #         expected_hash="hashed_value"
    #     ),
    #     Hash23AndMeFileTestData(
    #         file_path="/another/mock/file",
    #         mock_df_rows=[
    #             {"rsid": "rs3", "chromosome": "chr3", "position": "pos3", "genotype": "GG"},
    #             {"rsid": "rs4", "chromosome": "chr4", "position": "pos4", "genotype": "CC"}
    #         ],
    #         expected_concatenated_string="rs3:chr3:pos3:GG|rs4:chr4:pos4:CC",
    #         expected_hash="another_hashed_value"
    #     )
    # ])
    # @patch("pandas.read_csv")
    # @patch("hashlib.sha256")
    # def test_hash_23andme_file(self, mock_sha256, mock_read_csv, input_data):
    #     """Test hash_23andme_file with a mocked pandas read_csv."""
    #
    #     mock_df = MagicMock()
    #
    #     mock_df.apply.return_value = [f"{row['rsid']}:{row['chromosome']}:{row['position']}:{row['genotype']}"
    #                                   for row in input_data.mock_df_rows]
    #     mock_read_csv.return_value = mock_df
    #
    #     mock_hash_object = MagicMock()
    #     mock_hash_object.hexdigest.return_value = input_data.expected_hash
    #     mock_sha256.return_value = mock_hash_object
    #
    #     scorer = TwentyThreeWeFileScorer(input_data=[], config={}, requester=None, hasher=mock_sha256)
    #     result = scorer.hash_23andme_file(input_data.file_path)
    #
    #     mock_read_csv.assert_called_once_with(input_data.file_path, sep='\t', comment='#',
    #                                           names=['rsid', 'chromosome', 'position', 'genotype'])
    #
    #     mock_sha256.assert_called_once_with(input_data.expected_concatenated_string.encode())
    #     mock_hash_object.hexdigest.assert_called_once()
    #
    #     assert result == input_data.expected_hash

    @pytest.mark.parametrize("input_data", [
        InvalidGenotypesScoreTestData(total=0, low=1, high=3, expected_score=1.0),
        InvalidGenotypesScoreTestData(total=2, low=1, high=3, expected_score=0.5),
        InvalidGenotypesScoreTestData(total=3, low=1, high=3, expected_score=0.0)
    ])
    def test_invalid_genotypes_score(self, input_data):
        result = TwentyThreeWeFileScorer.invalid_genotypes_score(input_data.total, input_data.low, input_data.high)
        assert result == input_data.expected_score

    @pytest.mark.parametrize("input_data", [
        IndelScoreTestData(total=0, low=3, ultra_low=1, high=13, ultra_high=22, expected_score=0.0),
        IndelScoreTestData(total=2, low=3, ultra_low=1, high=13, ultra_high=22, expected_score=0.5),
        IndelScoreTestData(total=13, low=3, ultra_low=1, high=13, ultra_high=22, expected_score=1.0),
        IndelScoreTestData(total=18, low=3, ultra_low=1, high=13, ultra_high=22, expected_score=4/9),
        IndelScoreTestData(total=23, low=3, ultra_low=1, high=13, ultra_high=22, expected_score=0.0),
    ])
    def test_indel_score(self, input_data):
        result = TwentyThreeWeFileScorer.indel_score(input_data.total, input_data.low, input_data.ultra_low,
                                                     input_data.high, input_data.ultra_high)
        assert result == input_data.expected_score

    @pytest.mark.parametrize("input_data", [
        IRsidScoreTestData(total=0, low=5, high=25, expected_score=1.0),
        IRsidScoreTestData(total=15, low=5, high=25, expected_score=0.5),
        IRsidScoreTestData(total=30, low=5, high=25, expected_score=0.0)
    ])
    def test_i_rsid_score(self, input_data):
        result = TwentyThreeWeFileScorer.i_rsid_score(input_data.total, input_data.low, input_data.high)
        assert result == input_data.expected_score

    @pytest.mark.parametrize("input_data", [
        PercentVerifyScoreTestData(verified=90, all=100, low=0.9, ultra_low=0.85, high=0.96, ultra_high=0.98,
                                         expected_score=1.0),
        PercentVerifyScoreTestData(verified=80, all=100, low=0.9, ultra_low=0.85, high=0.96, ultra_high=0.98,
                                         expected_score=0.0),
        PercentVerifyScoreTestData(verified=85, all=100, low=0.9, ultra_low=0.85, high=0.96, ultra_high=0.98,
                                         expected_score=0.0),
        PercentVerifyScoreTestData(verified=97, all=100, low=0.9, ultra_low=0.85, high=0.96, ultra_high=0.98,
                                         expected_score=0.5),
        PercentVerifyScoreTestData(verified=88, all=100, low=0.9, ultra_low=0.85, high=0.96, ultra_high=0.98,
                                         expected_score=0.6),
    ])
    def test_percent_verification_score(self, input_data):
        result = TwentyThreeWeFileScorer.percent_verification_score(
            input_data.verified, input_data.all, input_data.low,
            input_data.ultra_low, input_data.high, input_data.ultra_high
        )
        assert result == input_data.expected_score

    @pytest.mark.parametrize("input_data", [
        HashSaveDataTestData(
            proof_response=ProofResponse(
                authenticity=0.95,
                ownership=0.85,
                uniqueness=0.9,
                quality=0.8,
                attributes={'total_score': 0.9, 'score_threshold': 0.85},
                valid=True,
                score=0.9,
                dlp_id=1234
            ),
            expected_hash_save_data={
                'sender_address': 'test_sender',
                'attestor_address': '',
                'tee_url': '',
                'job_id': '',
                'file_id': '',
                'profile_id': 'test_profile',
                'genome_hash': 'test_hash',
                'authenticity_score': 0.95,
                'ownership_score': 0.85,
                'uniqueness_score': 0.9,
                'quality_score': 0.8,
                'total_score': 0.9,
                'score_threshold': 0.85,
                'is_valid': True
            }
        ),
        HashSaveDataTestData(
            proof_response=ProofResponse(
                authenticity=0.5,
                ownership=0.4,
                uniqueness=0.6,
                quality=0.7,
                attributes={'total_score': 0.75, 'score_threshold': 0.7},
                valid=False,
                score=0.9,
                dlp_id=1234
            ),
            expected_hash_save_data={
                'sender_address': 'test_sender',
                'attestor_address': '',
                'tee_url': '',
                'job_id': '',
                'file_id': '',
                'profile_id': 'test_profile',
                'genome_hash': 'test_hash',
                'authenticity_score': 0.5,
                'ownership_score': 0.4,
                'uniqueness_score': 0.6,
                'quality_score': 0.7,
                'total_score': 0.75,
                'score_threshold': 0.7,
                'is_valid': False
            }
        )
    ])
    def test_generate_hash_save_data(self, input_data):
        scorer = TwentyThreeWeFileScorer(
            input_data=[],
            config={},
            requester=None,
            hasher=None
        )
        scorer.sender_address = 'test_sender'
        scorer.profile_id = 'test_profile'
        scorer.hash = 'test_hash'

        result = scorer.generate_hash_save_data(input_data.proof_response)

        assert result == input_data.expected_hash_save_data

    @pytest.mark.parametrize("input_data", [
        ProofOfOwnershipTestData(
            mock_verify_profile_response=True,
            expected_ownership_score=1.0
        ),
        ProofOfOwnershipTestData(
            mock_verify_profile_response=False,
            expected_ownership_score=0.0
        )
    ])
    def test_proof_of_ownership(self, input_data, monkeypatch):
        def mock_verify_profile(self):
            return input_data.mock_verify_profile_response

        monkeypatch.setattr(TwentyThreeWeFileScorer, 'verify_profile', mock_verify_profile)

        scorer = TwentyThreeWeFileScorer(input_data=[], config={}, requester=None, hasher=None)

        result = scorer.proof_of_ownership()

        assert result == input_data.expected_ownership_score

    @pytest.mark.parametrize("input_data", [
        ProofOfQualityTestData(
            dbsnp_verify_result={
                'invalid_genotypes': 1,
                'indels': 3,
                'i_rsids': 5,
                'dbsnp_verified': 90,
                'all': 100
            },
            expected_quality_score=0.7
        ),
        ProofOfQualityTestData(
            dbsnp_verify_result={
                'invalid_genotypes': 5,
                'indels': 10,
                'i_rsids': 20,
                'dbsnp_verified': 80,
                'all': 120
            },
            expected_quality_score=0.25
        )
    ])
    def test_proof_of_quality(self, input_data, mocker):
        sample_data = """rsid	chromosome	position	genotype
        rs137900170	1	1392325	GG
        rs138988486	1	1394069	CC
        rs111938039	1	1400170	GG
        rs182336567	1	1404796	--
        rs146343349	1	1412659	GG
        rs141143061	1	1417927	CC
        rs860213	1	1421991	--
        i713057	1	1425512	TT
        rs145313947	1	1425753	TT
        rs111509968	1	1446390	GG
        rs6690515	1	1447325	GG
        rs139049688	1	1449501	GG
        rs6669795	1	1450947	AA
        rs7531221	1	1453373	AA
        rs200101143	1	1464604	CC
        rs12032637	1	1465382	AA
        """
        sample_df = pd.read_csv(StringIO(sample_data), sep="\t")

        mock_dbsnp_handler = mocker.Mock()
        mock_dbsnp_handler.dbsnp_verify.return_value = input_data.dbsnp_verify_result

        mocker.patch.object(DbSNPHandler, 'load_data', return_value=sample_df)
        mocker.patch.object(DbSNPHandler, 'verify_snps', return_value=([], [], [], []))
        mocker.patch.object(DbSNPHandler, 'check_indels_and_i_rsids', return_value=input_data.dbsnp_verify_result)

        mocker.patch("my_proof.verify.DbSNPHandler", return_value=mock_dbsnp_handler)

        scorer = TwentyThreeWeFileScorer(input_data=[], config={'token': 'test-token', 'endpoint': 'test-endpoint'}, requester=None, hasher=None)
        result = scorer.proof_of_quality(filepath="dummy_filepath")

        assert result == pytest.approx(input_data.expected_quality_score, rel=1e-2)

    @pytest.mark.parametrize("input_data", [
        ProofOfUniquenessTestData(
            mock_hash_23andme_file_response="abc123hash",
            mock_verify_hash_response=True,
            expected_uniqueness_score=1.0
        ),
        ProofOfUniquenessTestData(
            mock_hash_23andme_file_response="xyz789hash",
            mock_verify_hash_response=False,
            expected_uniqueness_score=0.0
        )
    ])
    def test_proof_of_uniqueness(self, input_data, mocker):
        scorer = TwentyThreeWeFileScorer(input_data=[], config={}, requester=None, hasher=None)
        mocker.patch.object(scorer, 'hash_23andme_file', return_value=input_data.mock_hash_23andme_file_response)
        mocker.patch.object(scorer, 'verify_hash', return_value=input_data.mock_verify_hash_response)
        result = scorer.proof_of_uniqueness(filepath="dummy_path")

        assert result == input_data.expected_uniqueness_score

    @pytest.mark.parametrize("input_data", [
        ProofOfAuthenticityTestData(
            mock_check_header_response=True,
            mock_check_rsid_lines_response=True,
            expected_authenticity_score=1.0
        ),
        ProofOfAuthenticityTestData(
            mock_check_header_response=False,
            mock_check_rsid_lines_response=True,
            expected_authenticity_score=0.0
        ),
        ProofOfAuthenticityTestData(
            mock_check_header_response=True,
            mock_check_rsid_lines_response=False,
            expected_authenticity_score=0.0
        ),
        ProofOfAuthenticityTestData(
            mock_check_header_response=False,
            mock_check_rsid_lines_response=False,
            expected_authenticity_score=0.0
        )
    ])
    def test_proof_of_authenticity(self, input_data, mocker):
        scorer = TwentyThreeWeFileScorer(input_data=[], config={}, requester=None, hasher=None)
        mocker.patch.object(scorer, 'check_header', return_value=input_data.mock_check_header_response)
        mocker.patch.object(scorer, 'check_rsid_lines', return_value=input_data.mock_check_rsid_lines_response)
        result = scorer.proof_of_authenticity()

        assert result == input_data.expected_authenticity_score

    @pytest.mark.parametrize("input_data", [
        ReadHeaderTestData(
            input_data=[
                "# This data file generated by 23andMe at: Fri Oct 20 18:45:12 2024",
                "#",
                "# This file contains raw genotype data, including data that is not used in 23andMe reports.",
                "# This data has undergone a general quality review however only a subset of markers have been",
                "# individually validated for accuracy. As such, this data is suitable only for research,",
                "# educational, and informational use and not for medical or other use.",
                "#",
                "# Below is a text version of your data.  Fields are TAB-separated",
                "# Each line corresponds to a single SNP.  For each SNP, we provide its identifier",
                "# (an rsid or an internal id), its location on the reference human genome, and the",
                "# genotype call oriented with respect to the plus strand on the human reference sequence.",
                "# We are using reference human assembly build 37 (also known as Annotation Release 104).",
                "# Note that it is possible that data downloaded at different times may be different due to ongoing",
                "# improvements in our ability to call genotypes. More information about these changes can be found at:",
                "# https://you.23andme.com/p/a1b2c3d4e5f6g7h8/tools/data/download/",
                "#",
                "# More information on reference human assembly builds:",
                "# https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13/",
                "#",
                "# rsid	chromosome	position	genotype",
                "rs987654321	1	70000	AA",
                "rs234567890	1	567890	GG",
                "rs345678901	1	729000	CC",
                "rs456789012	1	753000	TT",
                "rs567890123	1	755000	AG",
                "rs678901234	1	757000	AA",
                "rs789012345	1	760000	TT",
                "rs890123456	1	770000	GG",
                "rs901234567	1	795000	AA",
                "rs012345678	1	802000	CC",
                "rs123456789	1	825000	GG",
                "rs234567891	1	831000	AA",
                "rs345678912	1	836000	TT",
                "rs456789123	1	840000	AG",
                "rs567890234	1	844000	TT"
            ],
            expected_header="""# This file contains raw genotype data, including data that is not used in 23andMe reports.
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
# rsid\tchromosome\tposition\tgenotype"""
        ),
    ])
    def test_read_header(self, input_data):
        scorer = TwentyThreeWeFileScorer(input_data=input_data.input_data, config={}, requester=None, hasher=None)

        result = scorer.read_header()

        assert result == input_data.expected_header

    @pytest.mark.parametrize("input_data", [
        Hash23AndMeFileTestData(
            input_data=pd.DataFrame({
                'rsid': ['rs123', 'rs456', 'rs789'],
                'chromosome': ['1', '2', '3'],
                'position': [123456, 234567, 345678],
                'genotype': ['AA', 'TT', 'GG']
            }),
            expected_concatenated_string="rs123:1:123456:AA|rs456:2:234567:TT|rs789:3:345678:GG",
            expected_hash="dummy_hash_1"
        ),
        Hash23AndMeFileTestData(
            input_data=pd.DataFrame({
                'rsid': ['rs987', 'rs654', 'rs321'],
                'chromosome': ['X', 'Y', 'MT'],
                'position': [987654, 654321, 321987],
                'genotype': ['CC', 'GG', 'TT']
            }),
            expected_concatenated_string="rs321:MT:321987:TT|rs654:Y:654321:GG|rs987:X:987654:CC",
            expected_hash="dummy_hash_2"
        )
    ])
    def test_hash_23andme_file(self, input_data, mocker):
        mocker.patch('pandas.read_csv', return_value=input_data.input_data)

        mock_hasher = Mock()
        mock_hasher.return_value.hexdigest.side_effect = [input_data.expected_hash]

        scorer = TwentyThreeWeFileScorer(input_data=[], config={}, requester=None, hasher=mock_hasher)

        result = scorer.hash_23andme_file(file_path="dummy_path")

        assert result == input_data.expected_hash

        concatenated_string = '|'.join(
            input_data.input_data.sort_values(by='rsid').apply(
                lambda row: f"{row['rsid']}:{row['chromosome']}:{row['position']}:{row['genotype']}", axis=1)
        )

        mock_hasher.assert_called_with(concatenated_string.encode())

    @pytest.mark.parametrize("input_data", [
        SaveHashTestData(
            proof_response={
                'authenticity': 0.9,
                'ownership': 0.8,
                'uniqueness': 0.95,
                'quality': 0.85,
                'attributes': {'total_score': 0.9, 'score_threshold': 0.8},
                'valid': True
            },
            expected_hash_data={
                'sender_address': 'test_sender',
                'attestor_address': '',
                'tee_url': '',
                'job_id': '',
                'file_id': '',
                'profile_id': 'test_profile',
                'genome_hash': 'test_hash',
                'authenticity_score': 0.9,
                'ownership_score': 0.8,
                'uniqueness_score': 0.95,
                'quality_score': 0.85,
                'total_score': 0.9,
                'score_threshold': 0.8,
                'is_valid': True
            },
            mock_response={'success': True},
            expected_success=True
        ),
        SaveHashTestData(
            proof_response={
                'authenticity': 0.5,
                'ownership': 0.4,
                'uniqueness': 0.6,
                'quality': 0.7,
                'attributes': {'total_score': 0.75, 'score_threshold': 0.7},
                'valid': False
            },
            expected_hash_data={
                'sender_address': 'test_sender',
                'attestor_address': '',
                'tee_url': '',
                'job_id': '',
                'file_id': '',
                'profile_id': 'test_profile',
                'genome_hash': 'test_hash',
                'authenticity_score': 0.5,
                'ownership_score': 0.4,
                'uniqueness_score': 0.6,
                'quality_score': 0.7,
                'total_score': 0.75,
                'score_threshold': 0.7,
                'is_valid': False
            },
            mock_response={'success': False},
            expected_success=False
        )
    ])
    def test_save_hash(self, input_data, mocker):
        # Mock generate_hash_save_data to return the expected hash data
        scorer = TwentyThreeWeFileScorer(input_data=[], config={'key': 'https://example.com/save'}, requester=None,
                                         hasher=None)
        mocker.patch.object(scorer, 'generate_hash_save_data', return_value=input_data.expected_hash_data)

        # Mock the requests.post to simulate the API call
        mock_post = mocker.patch('requests.post')
        mock_post.return_value.json.return_value = input_data.mock_response

        # Mock other attributes
        scorer.sender_address = 'test_sender'
        scorer.profile_id = 'test_profile'
        scorer.hash = 'test_hash'

        # Call the method
        result = scorer.save_hash(input_data.proof_response)

        # Assert the request was made with the correct data
        mock_post.assert_called_with(url='https://example.com/save', data=input_data.expected_hash_data)

        # Assert the result matches the expected success flag
        assert result == input_data.expected_success


class TestProof:

    @pytest.mark.parametrize("test_data", [
        GenerateTestData(file_list=['file1.txt'], expected_uniqueness=1.0, expected_ownership=1.0,
                         expected_authenticity=1.0, expected_quality=1.0, expected_valid=True),
        GenerateTestData(file_list=['file2.txt'], expected_uniqueness=0.9, expected_ownership=0.9,
                         expected_authenticity=0.9, expected_quality=0.9, expected_valid=True),
        GenerateTestData(file_list=['file3.txt'], expected_uniqueness=0.5, expected_ownership=0.5,
                         expected_authenticity=0.5, expected_quality=0.5, expected_valid=False),
    ])
    @mock.patch('os.listdir')
    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data="test data")
    @mock.patch('my_proof.proof.TwentyThreeWeFileScorer')
    def test_generate(self, mock_scorer_cls, mock_open, mock_listdir, test_data: GenerateTestData):
        # Mocking the list of input files
        mock_listdir.return_value = test_data.file_list

        # Mock the scorer instance
        mock_scorer = mock.Mock()
        mock_scorer.proof_of_uniqueness.return_value = test_data.expected_uniqueness
        mock_scorer.proof_of_ownership.return_value = test_data.expected_ownership
        mock_scorer.proof_of_authenticity.return_value = test_data.expected_authenticity
        mock_scorer.proof_of_quality.return_value = test_data.expected_quality
        mock_scorer.save_hash.return_value = True

        # Assign the mocked scorer to be returned when instantiating TwentyThreeWeFileScorer
        mock_scorer_cls.return_value = mock_scorer

        # Create a mock ProofResponse object without dlp_id
        mock_proof_response = ProofResponse(score=0, authenticity=0, ownership=0, uniqueness=0, quality=0, valid=False,
                                            attributes={'score': 0}, dlp_id=1234)

        # Set up the config and proof instance
        config = {'input_dir': '/input', 'dlp_id': 1234, 'key': 'some_key', 'verify': 'some_verify'}
        proof = Proof(config)
        proof.proof_response = mock_proof_response

        # Call the method to test
        proof_response = proof.generate()

        # Manually set the dlp_id in the proof_response (if needed)
        proof_response.metadata['dlp_id'] = config['dlp_id']

        # Assert that the scorer methods were called
        mock_scorer.proof_of_uniqueness.assert_called_once_with(filepath=f'/input/{test_data.file_list[0]}')
        mock_scorer.proof_of_ownership.assert_called_once()
        mock_scorer.proof_of_authenticity.assert_called_once()
        mock_scorer.proof_of_quality.assert_called_once_with(filepath=f'/input/{test_data.file_list[0]}')

        total_score = (test_data.expected_uniqueness + test_data.expected_ownership + test_data.expected_authenticity
                       + test_data.expected_quality) / 4
        assert proof_response.score == total_score
        assert proof_response.valid == test_data.expected_valid
        assert proof_response.attributes['total_score'] == total_score
        assert proof_response.attributes['score_threshold'] == 0.9

        # Assert that save_hash was called
        mock_scorer.save_hash.assert_called_once_with(proof_response)

        # Ensure the metadata is correct
        assert proof_response.metadata['dlp_id'] == 1234

