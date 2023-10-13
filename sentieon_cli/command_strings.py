"""
This module contains the functions that accept kwargs and return the
command strings.

We expect that the kwargs are created from user-input (to argh) or a config
file. Where appropriate, we use named args, but for flexibility, kwargs are
also used.

Command strings may be partial--that is, they could be mixed with other
command strings to get a full viable command.

"""
import io
import typing
from .logging import get_logger

logger = get_logger(__name__)


def cmd_variant_phaser(
    vcf: str,
    phased_bed: str,
    phased_vcf: str,
    phased_ext: str,
    kwargs: dict,
) -> str:
    """
    Cmd for --algo VariantPhaser
    """
    cmd = cmd_sentieon_driver(bed_key=None, skip_sample_input=False, **kwargs)

    cmd += f" --algo VariantPhaser -v {vcf} "
    cmd += f"--max_depth {kwargs.get('phase_max_depth', 1000)} "
    cmd += f"--out_bed {phased_bed} "
    cmd += f"--out_ext {phased_ext} "
    cmd += f"{phased_vcf} "
    return cmd


def cmd_bedtools_subtract(
    regions_bed: typing.Optional[typing.Union[str, io.TextIOWrapper]],
    phased_bed: str,
    unphased_bed: str,
    **kwargs,
):
    if regions_bed is None:
        # set region to the full genome
        with open(
            f"{kwargs['tmp_base']}_reference.bed", "wt", encoding="utf-8"
        ) as f:
            for line in open(
                name(kwargs["reference"]) + ".fai", encoding="utf-8"
            ):
                toks = line.strip().split("\t")
                f.write(f"{toks[0]}\t0\t{toks[1]}\n")
            regions_bed = f.name
    cmd = f"bedtools subtract -a {name(regions_bed)} -b {phased_bed} "
    cmd += f"> {unphased_bed}"
    return cmd


def cmd_repeat_model(phased_bed: str, phased_ext: str, kwargs) -> str:
    """
    Runs --algo RepeatModel
    """
    kwargs["phased_bed"] = phased_bed
    cmd = cmd_sentieon_driver(
        bed_key="phased_bed", skip_sample_input=False, **kwargs
    )
    kwargs["repeat_model"] = f"{kwargs['tmp_base']}/out_repeat.model"
    cmd += f" --read_filter PhasedReadFilter,phased_vcf={phased_ext}"
    cmd += ",phase_select=tag "
    cmd += "--algo RepeatModel --phased --min_map_qual 1 "
    cmd += "--min_group_count 10000 "
    cmd += "--read_flag_mask drop=supplementary --repeat_extension 5 "
    cmd += "--max_repeat_unit_size 2 --min_repeat_count 6 "
    cmd += kwargs["repeat_model"]
    return cmd


def cmd_model_apply(
    model: str, inp_vcf: str, out_vcf: str, kwargs: dict
) -> str:
    """
     sentieon driver -t "$_arg_threads" -r "$_arg_reference_fasta" \
        --algo DNAModelApply --model "$model" -v "$input_vcf" "$output_vcf"
    """
    cmd = cmd_sentieon_driver(bed_key=None, skip_sample_input=True, **kwargs)
    cmd += f"--algo DNAModelApply --model {model} -v {inp_vcf} {out_vcf}"
    return cmd


def name(path: typing.Union[str, io.TextIOWrapper]) -> str:
    """Return the name of a file that may also be a text-wrapper."""
    if hasattr(path, "name"):
        path = path.name
    return path


def cmd_sentieon_driver(
    bed_key: typing.Optional[str] = None,
    skip_sample_input: bool = False,
    **kwargs,
) -> str:
    """
    Common base for running sentieon driver.
    This is usually called along with other commands.
    NOTE: sometimes we need to run without bed file in later command
    whereas an earlier command might have a bed file.
    Same for read-filter.

    >>> d = {"regions": "phased.bed", "reference": "ref.fasta",
    ...      "sample_input": "sample.bam", "cores": 4}
    >>> cmd_sentieon_driver(bed_key="regions", skip_sample_input=False, **d)
    'sentieon driver -t 4 -r ref.fasta  --interval phased.bed -i sample.bam'
    >>> cmd_sentieon_driver(bed_key="regions", skip_sample_input=True, **d)
    'sentieon driver -t 4 -r ref.fasta  --interval phased.bed'

    >>> d['read-filter'] = 'PhasedReadFilter,phased_vcf=p.vcf.gz'
    >>> cmd_sentieon_driver(bed_key="regions", skip_sample_input=True, **d)
    'sentieon driver -t 4 -r ref.fasta  --interval phased.bed --read_filter \
PhasedReadFilter,phased_vcf=p.vcf.gz'

    """
    if bed_key is not None and kwargs.get(bed_key) is not None:
        bed = f" --interval {name(kwargs[bed_key])}"
    else:
        bed = ""
    if kwargs.get("read-filter"):
        read_filter = f" --read_filter {kwargs['read-filter']}"
    else:
        read_filter = ""

    cmd = (
        f"sentieon driver -t {kwargs['cores']} -r {name(kwargs['reference'])} "
    )
    cmd += f"{bed}"
    if not skip_sample_input:
        cmd += f" -i {name(kwargs['sample_input'])}"
    cmd += f"{read_filter}"
    return cmd


def cmd_pyexec_vcf_mod_haploid_patch(
    hap1_patch: str,
    hap2_patch: str,
    hap_patt: str,
    tech: str,
    phased_vcf: str,
    kwargs: dict,
) -> str:
    """
    merge dnascope and dnascope-hp variants

    >>> assert '--hap1 ' in cmd_pyexec_vcf_mod_haploid_patch("h1.vcf.gz",
    ... "h2.vcf.gz", "out_hap%d_%stmp.vcf.gz", "HiFi", None, {'cores': 2,
    ... 'vcf_mod_py': 'vcf_mod.py'})
    >>> assert not "--hap1 " in cmd_pyexec_vcf_mod_haploid_patch("h1.vcf.gz",
    ... "h2.vcf.gz", "out_hap%d_%stmp.vcf.gz", "ONT", "ph.vcf", {'cores': 2,
    ... 'vcf_mod_py': 'vcf_mod.py'})

    """
    assert tech in ("HiFi", "ONT")

    cmd = f"sentieon pyexec {kwargs['vcf_mod_py']} -t {kwargs['cores']} "
    cmd += "haploid_patch "
    cmd += f"--patch1 {hap1_patch} --patch2 {hap2_patch}"
    if tech == "HiFi":
        cmd += " --hap1 " + hap_patt % (1, "nohp_")
        cmd += " --hap2 " + hap_patt % (2, "nohp_")
    else:
        cmd += f" --phased {phased_vcf}"
    cmd += " --hap1_hp " + hap_patt % (1, "")
    cmd += " --hap2_hp " + hap_patt % (2, "")
    return cmd


def cmd_pyexec_vcf_mod_patch(
    out_vcf: str, vcf: str, vcf_hp: str, kwargs: dict
) -> str:
    """Patch DNAscope and DNAscopeHP VCF files"""

    cmd = f"sentieon pyexec {kwargs['vcf_mod_py']} -t {kwargs['cores']} "
    cmd += f"patch --vcf {vcf} --vcf_hp {vcf_hp} {out_vcf}"
    return cmd


def cmd_pyexec_gvcf_combine(gvcf: str, out_vcf: str, kwargs: dict) -> str:
    """Combine gVCF files"""

    cmd = f"sentieon pyexec {kwargs['gvcf_combine_py']} -t {kwargs['cores']} "
    cmd += f"{gvcf} {out_vcf} -"
    cmd += " | sentieon util vcfconvert - " + out_vcf.replace(
        ".vcf.gz", ".g.vcf.gz"
    )
    return cmd


def cmd_pyexec_vcf_mod_merge(
    hap1_vcf: str,
    hap2_vcf: str,
    unphased_vcf: str,
    phased_vcf: str,
    phased_bed: str,
    out_vcf: str,
    kwargs: dict,
) -> str:
    """Merge haploid VCF files"""

    cmd = f"sentieon pyexec {kwargs['vcf_mod_py']} -t {kwargs['cores']} "
    cmd += (
        f"merge --hap1 {hap1_vcf} --hap2 {hap2_vcf} --unphased {unphased_vcf} "
    )
    cmd += f"--phased {phased_vcf} --bed {phased_bed} {out_vcf}"

    return cmd


def cmd_algo_dnascope(
    model: str,
    out_vcf: str,
    kwargs: dict,
    bed_key: typing.Optional[str] = None,
    gvcf: typing.Optional[str] = None,
) -> str:
    """
    DNAscope sub-command DNAscopeHP is added in another command if applicable.
    """
    # TODO: this is used elsewhere, should create once and pass.
    # https://github.com/Sentieon/sentieon-scripts/blob/8d33f29e442d5a1e782445f06bc1f11e278d8f87/dnascope_LongRead/dnascope_HiFi.sh#L355-L359
    if gvcf:
        gvcf_str = (
            f" --algo DNAscope --model {kwargs['model_bundle']}/gvcf_model"
        )
        gvcf_str += f" --emit_mode gvcf {gvcf} "
    else:
        gvcf_str = ""
    if kwargs.get("dbsnp"):
        dbsnp = f" --dbsnp {kwargs['dbsnp'].name} "
    else:
        dbsnp = ""
    cmd = f" {gvcf_str}--algo DNAscope {dbsnp} --model {model} {out_vcf}"
    return cmd_sentieon_driver(bed_key, **kwargs) + cmd


def cmd_dnascope_hp(
    model: typing.Optional[str],
    repeat_model: str,
    hp_vcf: str,
    kwargs: dict,
) -> str:
    """
    DNAscopeHP sub-command.
    This only adds to an exist command, it does not prefix with the sentieon
      driver.

    For ONT, model should be None

    >>> d = {"dbsnp": "dbsnp.vcf.gz"}
    >>> cmd_dnascope_hp("haploid_hp_model", "repeat_model", "hp.vcf.gz", d)
    '--algo DNAscopeHP --dbsnp dbsnp.vcf.gz --model haploid_hp_model \
--pcr_indel_model repeat_model --min_repeat_count 6 hp.vcf.gz'
    >>> cmd_dnascope_hp(None, "repeat_model", "hp.vcf.gz", d)
    '--algo DNAscopeHP --dbsnp dbsnp.vcf.gz --pcr_indel_model repeat_model \
--min_repeat_count 6 hp.vcf.gz'
    """
    cmd = "--algo DNAscopeHP "
    if kwargs.get("dbsnp"):
        cmd += f"--dbsnp {name(kwargs['dbsnp'])} "
    if model is not None:
        cmd += f"--model {model} "
    cmd += f"--pcr_indel_model {repeat_model} --min_repeat_count 6 "
    cmd += hp_vcf

    return cmd
